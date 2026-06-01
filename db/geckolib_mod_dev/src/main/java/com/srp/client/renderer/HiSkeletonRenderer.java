package com.srp.client.renderer;

import com.srp.client.model.HiSkeletonModel;
import com.srp.entity.HiSkeletonEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class HiSkeletonRenderer extends GeoEntityRenderer<HiSkeletonEntity> {

    public HiSkeletonRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new HiSkeletonModel());
    }
}
