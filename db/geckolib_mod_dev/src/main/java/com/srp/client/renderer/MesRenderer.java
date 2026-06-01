package com.srp.client.renderer;

import com.srp.client.model.MesModel;
import com.srp.entity.MesEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class MesRenderer extends GeoEntityRenderer<MesEntity> {

    public MesRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new MesModel());
    }
}
