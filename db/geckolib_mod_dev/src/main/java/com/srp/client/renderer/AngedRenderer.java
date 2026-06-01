package com.srp.client.renderer;

import com.srp.client.model.AngedModel;
import com.srp.entity.AngedEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class AngedRenderer extends GeoEntityRenderer<AngedEntity> {

    public AngedRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new AngedModel());
    }
}
